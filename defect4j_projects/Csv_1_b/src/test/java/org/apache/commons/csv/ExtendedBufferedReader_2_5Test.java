package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Field;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_2_5Test {

    private ExtendedBufferedReader extendedBufferedReader;
    private Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = new Reader() {
            private final char[] data = "abc\ndef".toCharArray();
            private int pos = 0;

            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                if (pos >= data.length) {
                    return -1;
                }
                int charsToRead = Math.min(len, data.length - pos);
                System.arraycopy(data, pos, cbuf, off, charsToRead);
                pos += charsToRead;
                return charsToRead;
            }

            @Override
            public void close() throws IOException { }
        };
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testReadReturnsCharAndIncrementsLineCounterOnNewline() throws IOException {
        // read 'a'
        int ch = extendedBufferedReader.read();
        assertEquals('a', ch);

        // read 'b'
        ch = extendedBufferedReader.read();
        assertEquals('b', ch);

        // read 'c'
        ch = extendedBufferedReader.read();
        assertEquals('c', ch);

        // read '\n'
        ch = extendedBufferedReader.read();
        assertEquals('\n', ch);

        // verify lineCounter incremented via reflection
        int lineCounter = getPrivateField(extendedBufferedReader, "lineCounter");
        assertEquals(1, lineCounter);

        // verify lastChar updated via reflection
        int lastChar = getPrivateField(extendedBufferedReader, "lastChar");
        assertEquals('\n', lastChar);
    }

    @Test
    @Timeout(8000)
    void testReadReturnsEndOfStream() throws IOException {
        // read until end of stream
        int ch;
        do {
            ch = extendedBufferedReader.read();
        } while (ch != -1);

        assertEquals(-1, ch);

        int lineCounter = getPrivateField(extendedBufferedReader, "lineCounter");
        // There is one newline in the data "abc\ndef"
        assertEquals(1, lineCounter);

        int lastChar = getPrivateField(extendedBufferedReader, "lastChar");
        assertEquals(-1, lastChar);
    }

    private int getPrivateField(ExtendedBufferedReader instance, String fieldName) {
        try {
            Field field = ExtendedBufferedReader.class.getDeclaredField(fieldName);
            field.setAccessible(true);
            return field.getInt(instance);
        } catch (ReflectiveOperationException e) {
            throw new RuntimeException(e);
        }
    }
}