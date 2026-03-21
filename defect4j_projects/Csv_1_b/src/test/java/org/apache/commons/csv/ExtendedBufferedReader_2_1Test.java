package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;

class ExtendedBufferedReader_2_1Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testRead_notNewLine() throws IOException {
        when(mockReader.read()).thenReturn((int) 'a');

        int result = extendedBufferedReader.read();

        assertEquals('a', result);
        assertEquals(0, getPrivateField(extendedBufferedReader, "lineCounter"));
        assertEquals('a', getPrivateField(extendedBufferedReader, "lastChar"));
    }

    @Test
    @Timeout(8000)
    void testRead_newLine() throws IOException {
        when(mockReader.read()).thenReturn((int) '\n');

        int result = extendedBufferedReader.read();

        assertEquals('\n', result);
        assertEquals(1, getPrivateField(extendedBufferedReader, "lineCounter"));
        assertEquals('\n', getPrivateField(extendedBufferedReader, "lastChar"));
    }

    @Test
    @Timeout(8000)
    void testRead_endOfStream() throws IOException {
        when(mockReader.read()).thenReturn(-1);

        int result = extendedBufferedReader.read();

        assertEquals(-1, result);
        assertEquals(0, getPrivateField(extendedBufferedReader, "lineCounter"));
        assertEquals(-2, getPrivateField(extendedBufferedReader, "lastChar")); // UNDEFINED is -2
    }

    private int getPrivateField(ExtendedBufferedReader instance, String fieldName) {
        try {
            Field field = ExtendedBufferedReader.class.getDeclaredField(fieldName);
            field.setAccessible(true);
            return field.getInt(instance);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}