package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;
import java.io.IOException;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.Reader;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_7_1Test {

    private ExtendedBufferedReader extendedBufferedReader;

    @BeforeEach
    void setUp() {
        Reader reader = new Reader() {
            @Override
            public int read(char[] cbuf, int off, int len) {
                return -1; // simulate end of stream
            }
            @Override
            public void close() {
            }
        };
        extendedBufferedReader = new ExtendedBufferedReader(reader);
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber_DefaultValue() throws Exception {
        // Using reflection to access getLineNumber method
        Method getLineNumberMethod = ExtendedBufferedReader.class.getDeclaredMethod("getLineNumber");
        getLineNumberMethod.setAccessible(true);

        // Default lineCounter is 0
        int lineNumber = (int) getLineNumberMethod.invoke(extendedBufferedReader);
        assertEquals(0, lineNumber);
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber_AfterSettingLineCounter() throws Exception {
        // Set lineCounter to a specific value via reflection
        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        lineCounterField.setInt(extendedBufferedReader, 42);

        Method getLineNumberMethod = ExtendedBufferedReader.class.getDeclaredMethod("getLineNumber");
        getLineNumberMethod.setAccessible(true);

        int lineNumber = (int) getLineNumberMethod.invoke(extendedBufferedReader);
        assertEquals(42, lineNumber);
    }
}