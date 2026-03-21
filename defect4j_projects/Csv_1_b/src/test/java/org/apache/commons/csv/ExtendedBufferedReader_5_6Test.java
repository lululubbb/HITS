package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Field;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_5_6Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader) {
            @Override
            public String readLine() throws IOException {
                return super.readLine();
            }
        };
    }

    @Test
    @Timeout(8000)
    void testReadLine_NonNullNonEmptyLine() throws Exception {
        ExtendedBufferedReader reader = new ExtendedBufferedReader(new Reader() {
            private boolean returned = false;

            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                if (!returned) {
                    String str = "Hello\n";
                    int length = Math.min(len, str.length());
                    str.getChars(0, length, cbuf, off);
                    returned = true;
                    return length;
                }
                return -1;
            }

            @Override
            public void close() throws IOException {
            }
        });

        String line = reader.readLine();
        assertEquals("Hello", line);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = (int) lastCharField.get(reader);
        assertEquals('o', lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = (int) lineCounterField.get(reader);
        assertEquals(1, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_NonNullEmptyLine() throws Exception {
        ExtendedBufferedReader reader = new ExtendedBufferedReader(new Reader() {
            private boolean returned = false;

            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                if (!returned) {
                    String str = "\n";
                    int length = Math.min(len, str.length());
                    str.getChars(0, length, cbuf, off);
                    returned = true;
                    return length;
                }
                return -1;
            }

            @Override
            public void close() throws IOException {
            }
        });

        String line = reader.readLine();
        assertEquals("", line);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = (int) lastCharField.get(reader);
        assertEquals(ExtendedBufferedReader.UNDEFINED, lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = (int) lineCounterField.get(reader);
        assertEquals(1, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_NullLine() throws Exception {
        ExtendedBufferedReader reader = new ExtendedBufferedReader(new Reader() {
            @Override
            public int read(char[] cbuf, int off, int len) throws IOException {
                return -1;
            }

            @Override
            public void close() throws IOException {
            }
        });

        String line = reader.readLine();
        assertNull(line);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = (int) lastCharField.get(reader);
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = (int) lineCounterField.get(reader);
        assertEquals(0, lineCounter);
    }
}